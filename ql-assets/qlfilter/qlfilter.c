#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/in.h>
#include <linux/ip.h>
#include <linux/ipv6.h>
#include <linux/udp.h>

#include <stdint.h>

#define SEC(NAME) __attribute__((section(NAME), used))

#define htons(x) ((__be16)___constant_swab16((x)))
#define htonl(x) ((__be32)___constant_swab32((x)))

SEC("prog")
int xdp_drop_q3ql_udp_reflections(struct xdp_md *ctx)
{
	void *data_end = (void *)(long)ctx->data_end;
	void *data = (void *)(long)ctx->data;
	struct ethhdr *eth = data;

	uint64_t nh_off = sizeof(*eth);
	if (data + nh_off > data_end) {
		return XDP_PASS;
	}

	uint16_t h_proto = eth->h_proto;
	int i;

	// IPv4 Inspection
	if (h_proto == htons(ETH_P_IP)) {
		struct iphdr *iph = data + nh_off;
		struct udphdr *udph = data + nh_off + sizeof(struct iphdr);
		if (udph + 1 > (struct udphdr *)data_end) {
			return XDP_PASS;
		}
		// If the destination port within the range 27960-27979 and the sourceport is under 1024, drop the packet.
		if (iph->protocol == IPPROTO_UDP && udph->dest >= htons(27960) && udph->dest <= htons(27979)){
			if (htons(udph->source) <= 1024){
				return XDP_DROP;
			} else if (htons(udph->source) == 1900){
				return XDP_DROP;
			} else {
				return XDP_PASS;
			}
		}
		// If UDP packet is fragmented, drop it.
		if (iph->protocol == IPPROTO_UDP && iph->frag_off != 0) {
			return XDP_DROP;
		}
		// Pass all other traffic.
		return XDP_PASS;
	}
	// Pass anything else out of the above scope.
	return XDP_PASS;
}

char _license[] SEC("license") = "GPL";